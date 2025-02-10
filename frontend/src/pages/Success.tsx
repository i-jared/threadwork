import { ProjectList } from '../components/ProjectList'
import { useEffect } from 'react'

export default function SuccessPage() {
  console.log('Success page rendering')

  useEffect(() => {
    console.log('Success page mounted')
    return () => {
      console.log('Success page unmounting')
    }
  }, [])

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-8">Success!</h1>
      <p className="mb-4">Your project has been successfully completed.</p>
      <a href="#" className="text-blue-500 hover:underline mb-4 block">Download your file from S3</a>
      <button type="button" className="bg-blue-500 text-white px-4 py-2 rounded mb-8">
        Start New Project
      </button>
      
      <div className="mt-8">
        <ProjectList />
      </div>
    </div>
  )
} 