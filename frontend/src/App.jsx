import React from 'react'
import './App.css'

function App() {
  return (
    <div className="min-h-screen bg-glytch-dark text-white">
      <header className="p-4">
        <h1 className="text-3xl font-glytch text-glytch-pink">
          🪩 GlytchDraft
        </h1>
        <p className="text-glytch-blue">The Co-Evolution Engine</p>
      </header>
      
      <main className="p-4">
        <div className="text-center">
          <p className="text-lg mb-4">
            Choose your Order. Meet your AI Homie. Co-create meaning.
          </p>
          <button className="bg-glytch-purple text-glytch-dark px-6 py-3 rounded font-bold hover:scale-105 transition-transform">
            Enter the Glytch
          </button>
        </div>
      </main>
    </div>
  )
}

export default App
