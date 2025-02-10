import { ProjectList } from '../components/ProjectList'
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Download, Plus } from "lucide-react"
import { Link } from 'react-router-dom'

export default function SuccessPage() {
  return (
    <div className="container mx-auto p-4 space-y-8">
      <Card className="bg-gradient-to-r from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/10">
        <CardHeader>
          <CardTitle className="text-3xl">Success!</CardTitle>
          <CardDescription>Your project has been successfully completed.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" className="w-full sm:w-auto" asChild>
            <Link to="#" className="inline-flex items-center">
              <Download className="mr-2 h-4 w-4" />
              Download from S3
            </Link>
          </Button>
          
          <Button className="w-full sm:w-auto ml-0 sm:ml-4" asChild>
            <Link to="/new-project" className="inline-flex items-center">
              <Plus className="mr-2 h-4 w-4" />
              Start New Project
            </Link>
          </Button>
        </CardContent>
      </Card>
      
      <div className="mt-8">
        <ProjectList />
      </div>
    </div>
  )
} 