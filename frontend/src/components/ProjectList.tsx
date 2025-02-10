import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"

interface Project {
  id: number
  user_id: string
  project_data: {
    name: string
    description: string
    status: string
  }
  created_at: string
}

export function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  console.log('ProjectList component rendering')

  useEffect(() => {
    console.log('ProjectList component mounted')
    
    async function fetchProjects() {
      console.log('Fetching projects...')
      try {
        const { data, error } = await supabase
          .from('projects')
          .select(`
            id,
            user_id,
            project_data,
            created_at
          `)
          .order('created_at', { ascending: false })
          .throwOnError()
        
        console.log('Projects fetched:', data, error)

        if (error) throw error

        setProjects(data || [])
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Failed to fetch projects'
        console.error('Error fetching projects:', message)
        setError(message)
      } finally {
        setLoading(false)
      }
    }

    fetchProjects()

    return () => {
      console.log('ProjectList component unmounting')
    }
  }, [])

  if (loading) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-bold">Projects</h2>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-4 w-[250px]" />
                <Skeleton className="h-4 w-[200px]" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-[300px]" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Error</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Projects ({projects.length})</h2>
      <ScrollArea className="h-[600px] rounded-md border">
        <div className="p-4 space-y-4">
          {projects.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">No projects found</p>
              </CardContent>
            </Card>
          ) : (
            projects.map((project) => (
              <Card key={project.id}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{project.project_data?.name || 'Unnamed Project'}</CardTitle>
                    <Badge variant={
                      project.project_data?.status === 'completed' ? 'success' :
                      project.project_data?.status === 'in_progress' ? 'default' :
                      'secondary'
                    }>
                      {project.project_data?.status || 'Unknown'}
                    </Badge>
                  </div>
                  <CardDescription>
                    {new Date(project.created_at).toLocaleDateString()}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground">
                    {project.project_data?.description || 'No description'}
                  </p>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
} 