import { Navbar } from './Navbar'

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main>
        {children}
      </main>
    </div>
  )
} 