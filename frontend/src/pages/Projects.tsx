import { ProjectList } from '../components/ProjectList'
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Download, Plus, Sparkles } from "lucide-react"
import { Link } from 'react-router-dom'
import { motion } from "framer-motion"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"

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

export default function ProjectsPage() {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="container mx-auto p-4 space-y-8"
    >
      <motion.div variants={item} className="flex justify-between items-center">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground">Manage and track all your projects in one place</p>
        </div>
        <Button asChild>
          <Link to="/" className="inline-flex items-center">
            <Plus className="mr-2 h-4 w-4" />
            New Project
          </Link>
        </Button>
      </motion.div>

      <motion.div variants={item}>
        <Card className="bg-gradient-to-r from-primary/5 via-primary/10 to-primary/5 dark:from-primary/10 dark:via-primary/15 dark:to-primary/10 overflow-hidden relative">
          <div className="absolute inset-0 bg-grid-white/10 [mask-image:linear-gradient(0deg,white,rgba(255,255,255,0.6))] dark:[mask-image:linear-gradient(0deg,rgba(255,255,255,0.1),rgba(255,255,255,0.5))]" />
          <CardHeader>
            <div className="flex items-center space-x-2">
              <CardTitle className="text-2xl">Latest Project</CardTitle>
              <Badge variant="secondary" className="font-normal">
                <Sparkles className="mr-1 h-3 w-3" />
                New
              </Badge>
            </div>
            <CardDescription>Your most recent project has been completed</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <Button variant="secondary" className="group" asChild>
                <Link to="#" className="inline-flex items-center">
                  <Download className="mr-2 h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
                  Download from S3
                </Link>
              </Button>
              
              <Button className="group" asChild>
                <Link to="/" className="inline-flex items-center">
                  <Plus className="mr-2 h-4 w-4 transition-transform group-hover:rotate-90" />
                  Start New Project
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
      
      <Separator className="my-8" />
      
      <motion.div variants={item}>
        <Card>
          <CardHeader>
            <CardTitle>All Projects</CardTitle>
            <CardDescription>View and manage all your projects</CardDescription>
          </CardHeader>
          <CardContent>
            <ProjectList />
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  )
} 