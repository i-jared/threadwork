import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { useAuth } from '@/lib/auth-context'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import { CreditCard, Sparkles, AlertCircle } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"

interface CreditInfo {
  credit_amount: number
  updated_at: string
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
}

export default function BillingPage() {
  const { user } = useAuth()
  const [credits, setCredits] = useState<CreditInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchCredits() {
      if (!user) return

      try {
        const { data, error: fetchError } = await supabase
          .from('credits')
          .select('credit_amount, updated_at')
          .eq('user_id', user.id)
          .maybeSingle()

        if (fetchError) {
          setError('Unable to load credits')
        } else {
          setCredits(data || { credit_amount: 0, updated_at: new Date().toISOString() })
        }
      } catch (e) {
        setError('Unable to load credits')
      } finally {
        setLoading(false)
      }
    }

    fetchCredits()
  }, [user])

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show" 
      className="container mx-auto p-4 max-w-2xl space-y-8"
    >
      <motion.div variants={item} className="space-y-2">
        <div className="flex items-center space-x-2">
          <h1 className="text-3xl font-bold tracking-tight">Billing & Credits</h1>
          <Badge variant="secondary" className="font-normal">
            <CreditCard className="mr-1 h-3 w-3" />
            Manage
          </Badge>
        </div>
        <p className="text-muted-foreground">
          View your credit balance and manage your billing
        </p>
      </motion.div>

      {error && (
        <motion.div variants={item}>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </motion.div>
      )}

      <motion.div variants={item}>
        <Card className="border-2">
          <CardHeader>
            <CardTitle>Credit Balance</CardTitle>
            <CardDescription>Your current credit balance and usage</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex justify-between items-center p-4 bg-primary/5 rounded-lg">
              <h2 className="text-xl font-semibold">Available Credits</h2>
              <div className="text-right">
                <div className="text-3xl font-bold tracking-tight">
                  {loading ? (
                    <span className="inline-block w-16 h-8 bg-muted animate-pulse rounded" />
                  ) : (
                    <span className="flex items-center space-x-2">
                      <Sparkles className="h-5 w-5 text-primary" />
                      <span>{credits?.credit_amount || 0}</span>
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Last updated: {credits?.updated_at ? new Date(credits.updated_at).toLocaleDateString() : 'Never'}
                </p>
              </div>
            </div>
          </CardContent>
          <CardFooter className="bg-card border-t pt-6">
            <Button className="w-full sm:w-auto group" asChild>
              <Link to="#">
                <CreditCard className="mr-2 h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
                Purchase More Credits
              </Link>
            </Button>
          </CardFooter>
        </Card>
      </motion.div>

      <motion.div variants={item}>
        <Card>
          <CardHeader>
            <CardTitle>Usage History</CardTitle>
            <CardDescription>Track your credit usage over time</CardDescription>
          </CardHeader>
          <CardContent className="h-48 flex items-center justify-center text-muted-foreground">
            Usage history coming soon...
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  )
} 