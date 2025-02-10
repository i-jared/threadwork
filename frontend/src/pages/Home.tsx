import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

export default function HomePage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [projectDescription, setProjectDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  console.log('HomePage: Component rendering')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('HomePage: Submitting project')
    setLoading(true)
    setError(null)

    try {
      // Check credits first
      const { data: credits, error: creditsError } = await supabase
        .from('credits')
        .select('credit_amount')
        .single()

      if (creditsError) throw creditsError
      console.log('HomePage: Credits checked:', credits)

      if (!credits || credits.credit_amount < 1) {
        console.log('HomePage: Insufficient credits')
        navigate('/billing')
        return
      }

      // Create project
      const response = await fetch('http://localhost:8000/create-project', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description: projectDescription }),
      })

      if (!response.ok) throw new Error('Failed to create project')
      
      console.log('HomePage: Project created successfully')
      navigate('/success')
    } catch (e) {
      console.error('HomePage: Error:', e)
      setError(e instanceof Error ? e.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container mx-auto p-4 max-w-2xl">
      <h1 className="text-3xl font-bold mb-8">Create New Project</h1>
      
      {error && (
        <div className="mb-4 p-4 bg-red-50 text-red-500 rounded-lg">
          Error: {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label 
            htmlFor="projectDescription" 
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Describe Your Project
          </label>
          <textarea
            id="projectDescription"
            value={projectDescription}
            onChange={(e) => setProjectDescription(e.target.value)}
            className="w-full h-32 p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Describe what you want to create..."
            required
          />
        </div>

        <div className="flex items-center justify-between">
          <button
            type="submit"
            disabled={loading}
            className={`px-4 py-2 rounded-lg text-white ${
              loading 
                ? 'bg-blue-300 cursor-not-allowed' 
                : 'bg-blue-500 hover:bg-blue-600'
            }`}
          >
            {loading ? 'Creating Project...' : 'Create Project'}
          </button>

          <button
            type="button"
            onClick={() => navigate('/billing')}
            className="text-blue-500 hover:underline"
          >
            Check Credits
          </button>
        </div>
      </form>

      {loading && (
        <div className="mt-8">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            <div className="h-4 bg-gray-200 rounded w-5/6"></div>
          </div>
          <p className="mt-4 text-sm text-gray-500">
            Processing your request... This may take a few moments.
          </p>
        </div>
      )}
    </div>
  )
} 