import { supabase } from './supabase'
import JSZip from 'jszip'

export async function createAndUploadProjectZip(
  projectId: string,
  files: { name: string; content: string }[]
): Promise<string | null> {
  try {
    // Get or create bucket for project
    const { data: { bucket_name }, error: bucketError } = await supabase
      .rpc('create_project_bucket', { project_id: projectId })
    
    if (bucketError) throw bucketError
    
    // Create a new ZIP file
    const zip = new JSZip()
    
    // Add all files to the zip
    files.forEach(file => {
      zip.file(file.name, file.content)
    })
    
    // Generate ZIP blob
    const zipBlob = await zip.generateAsync({ type: 'blob' })
    
    // Upload to project-specific bucket
    const fileName = `project-${projectId}.zip`
    const { data, error } = await supabase.storage
      .from(bucket_name)
      .upload(fileName, zipBlob, {
        contentType: 'application/zip',
        upsert: true
      })
      
    if (error) {
      console.error('Error uploading zip:', error)
      return null
    }
    
    // Generate download URL from project-specific bucket
    const { data: { publicUrl } } = supabase.storage
      .from(bucket_name)
      .getPublicUrl(fileName)
      
    return publicUrl
  } catch (error) {
    console.error('Error creating zip:', error)
    return null
  }
}

export async function getProjectDownloadUrl(projectId: string): Promise<string | null> {
  const fileName = `project-${projectId}.zip`
  const { data: { publicUrl } } = supabase.storage
    .from('project-files')
    .getPublicUrl(fileName)
  
  return publicUrl
} 