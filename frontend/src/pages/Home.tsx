import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AlertCircle, Loader2, CreditCard } from "lucide-react"
import { Label } from "@/components/ui/label"

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
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="projectDescription">
                Describe Your Project
              </Label>
              <Textarea
                id="projectDescription"
                value={projectDescription}
                onChange={(e) => setProjectDescription(e.target.value)}
                className="h-32"
                placeholder="Describe what you want to create..."
                required
              />
            </div>

            <div className="flex items-center justify-between">
              <Button 
                type="submit" 
                disabled={loading}
                className="w-full sm:w-auto"
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {loading ? 'Creating Project...' : 'Create Project'}
              </Button>

              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/billing')}
                className="w-full sm:w-auto sm:ml-4"
              >
                <CreditCard className="mr-2 h-4 w-4" />
                Check Credits
              </Button>
            </div>
          </form>

          {loading && (
            <div className="mt-8 space-y-4">
              <div className="space-y-2">
                <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
                <div className="h-4 bg-muted animate-pulse rounded w-1/2" />
                <div className="h-4 bg-muted animate-pulse rounded w-5/6" />
              </div>
              <p className="text-sm text-muted-foreground">
                Processing your request... This may take a few moments.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
} 