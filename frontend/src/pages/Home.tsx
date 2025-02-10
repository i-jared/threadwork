import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AlertCircle, Loader2, CreditCard, Sparkles } from "lucide-react"
import { Label } from "@/components/ui/label"
import { motion, AnimatePresence } from "framer-motion"
import { Badge } from "@/components/ui/badge"

export default function HomePage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [projectDescription, setProjectDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      // Check credits first
      const { data: credits, error: creditsError } = await supabase
        .from('credits')
        .select('credit_amount')
        .single()

      if (creditsError) throw creditsError

      if (!credits || credits.credit_amount < 1) {
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
      
      navigate('/success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="container mx-auto p-4 max-w-2xl"
    >
      <div className="space-y-2 mb-8">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="flex items-center space-x-2"
        >
          <h1 className="text-3xl font-bold tracking-tight">Create New Project</h1>
          <Badge variant="secondary" className="font-normal">
            <Sparkles className="mr-1 h-3 w-3" />
            AI Powered
          </Badge>
        </motion.div>
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-muted-foreground"
        >
          Describe your project and let our AI handle the rest
        </motion.p>
      </div>
      
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-6"
          >
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="border-2">
          <CardHeader>
            <CardTitle>Project Details</CardTitle>
            <CardDescription>
              Be as specific as possible in your description
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="projectDescription" className="text-base">
                  Project Description
                </Label>
                <Textarea
                  id="projectDescription"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  className="h-32 resize-none transition-all duration-200 focus:ring-2 focus:ring-primary !rounded-lg"
                  placeholder="Describe what you want to create..."
                  required
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <Button 
                  type="submit" 
                  disabled={loading}
                  className="group relative"
                >
                  {loading ? (
                    <span className="flex items-center">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating Project...
                    </span>
                  ) : (
                    <span className="flex items-center">
                      <Sparkles className="mr-2 h-4 w-4 transition-all group-hover:rotate-12" />
                      Create Project
                    </span>
                  )}
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate('/billing')}
                  className="group"
                >
                  <CreditCard className="mr-2 h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
                  Check Credits
                </Button>
              </div>
            </form>

            {loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mt-8 space-y-4"
              >
                <div className="space-y-2">
                  <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
                  <div className="h-4 bg-muted animate-pulse rounded w-1/2" />
                  <div className="h-4 bg-muted animate-pulse rounded w-5/6" />
                </div>
                <p className="text-sm text-muted-foreground">
                  Processing your request... This may take a few moments.
                </p>
              </motion.div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  )
} 