import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

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

  if (loading) return <div className="p-4">Loading projects...</div>
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Projects ({projects.length})</h2>
      {projects.length === 0 ? (
        <p>No projects found</p>
      ) : (
        <div className="grid gap-4">
          {projects.map((project) => (
            <div key={project.id} className="p-4 border rounded-lg hover:bg-gray-50">
              <h3 className="font-semibold">{project.project_data?.name || 'Unnamed Project'}</h3>
              <p className="text-gray-600">{project.project_data?.description || 'No description'}</p>
              <div className="mt-2 flex items-center gap-2">
                <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                  ${project.project_data?.status === 'completed' ? 'bg-green-100 text-green-800' : 
                    project.project_data?.status === 'in_progress' ? 'bg-blue-100 text-blue-800' : 
                    'bg-gray-100 text-gray-800'}`}>
                  {project.project_data?.status || 'Unknown'}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
} 